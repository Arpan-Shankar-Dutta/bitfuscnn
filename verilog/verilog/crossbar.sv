module crossbar
  #(parameter integer RAM_WIDTH = 14,
    parameter integer BANK_COUNT = 256,
    parameter integer TILE_SIZE = 256,
    parameter integer INDEX_WIDTH = 4)(
    input wire clk,
    input wire reset_n,
    input wire[1:0] bitwidth,
   
    //Input from multiplier array
    input wire[63:0] products[16],
    
    //Inputs from coordinate computation
    input wire[7:0] row_coordinate[TILE_SIZE],
    input wire[7:0] column_coordinate[TILE_SIZE],
    
    //Buffer bank interface
    output logic [$clog2(TILE_SIZE)-1:0] buffer_row_write[BANK_COUNT],
    output logic [$clog2(TILE_SIZE)-1:0] buffer_column_write[BANK_COUNT],
    output logic [7:0] buffer_data_write[BANK_COUNT],
    output logic buffer_write_enable[BANK_COUNT],
    
    //cross bar stall signal
    output logic crossbar_stall
  );

integer i;
logic [$clog2(TILE_SIZE)-1:0] next_buffer_row_write[BANK_COUNT];
logic [$clog2(TILE_SIZE)-1:0] next_buffer_column_write[BANK_COUNT];
logic [7:0] next_buffer_data_write[BANK_COUNT];
logic next_buffer_write_enable[BANK_COUNT];
logic [BANK_COUNT-1:0] used_banks; //Keep track of which banks have been used in a single cycle
logic [$clog2(BANK_COUNT)-1:0] bank;
logic [TILE_SIZE-1:0] inputs_sent; //Accumulate inputs set so far over multiple cycles
logic [TILE_SIZE-1:0] next_inputs_sent; //Track inputs processed in one cycle
logic next_crossbar_stall;

//Internal regs to store inputs over multiple cycles
logic [7:0] internal_row_coordinate[TILE_SIZE];
logic [7:0] internal_column_coordinate[TILE_SIZE];
logic [63:0] interal_products[16];


function logic [$clog2(BANK_COUNT)-1:0] bank_from_rc(
    input logic[$clog2(TILE_SIZE)-1:0] row,
    input logic[$clog2(TILE_SIZE)-1:0] column);
  logic [$clog2(BANK_COUNT)-1:0] shift;
  logic [$clog2(TILE_SIZE)-1:0] row_upper;
  logic [$clog2(TILE_SIZE)-1:0] row_section;
  logic [$clog2(BANK_COUNT)-1:0] small_buffer_count;
  row_upper = row >> bitwidth;
  row_section = row % (1 << bitwidth);
  small_buffer_count = BANK_COUNT >> bitwidth;
  shift = (row_upper * 3) % BANK_COUNT;
  bank_from_rc = (column + shift + row_section * small_buffer_count) % BANK_COUNT;
endfunction


function logic [$clog2(TILE_SIZE)-1:0] entry_from_rc(
    input logic[$clog2(TILE_SIZE)-1:0] row,
    input logic[$clog2(TILE_SIZE)-1:0] column);
  entry_from_rc = row >> bitwidth;
endfunction


always_comb begin
  used_banks = 0;
  next_crossbar_stall = 0;
  next_inputs_sent = 0;
  for(i = 0; i<BANK_COUNT; i++) begin
    next_buffer_write_enable[i] = 0;
  end // end for
  case(bitwidth)
  2'b10:
    begin
      for(i = 0; i<15; i++) begin
        // Compute bank that a row,column goes to 
        bank = bank_from_rc(row_coordinate[i], column_coordinate[i]);
        // If bank hasn't been sent to and, 
        // the input hasn't already been sent in a previous cycle
        if(!used_banks[bank] && !inputs_sent[i]) begin
          next_buffer_row_write[bank] = row_coordinate[i];
          next_buffer_column_write[bank] = column_coordinate[i];
          // Truncate to 8 bits, since accumulator stores 8 bit values only
          next_buffer_data_write[bank] = {products[i][63], products[i][6:0]}; 
          next_buffer_write_enable[bank] = 1;
          used_banks[bank] = 1; // Mark bank as used 
          next_inputs_sent[i] = 1; //Mark input as processed
        end // end if
      end // end for
    end // end case for bitwidth = 2 ie 8 bit mode of operation
  default: // default case make all zero. Some synthesis thing that Arpan and Max mentioned.
    begin
      for(i = 0; i<BANK_COUNT; i++) begin
        next_buffer_row_write[i] = 0;
        next_buffer_column_write[i] = 0;
        next_buffer_data_write[i] = 0; 
        next_buffer_write_enable[i] = 0;
      end // end for
      used_banks = 0;
      next_inputs_sent = 0;
    end // end default case 
  endcase
end

/*
//Buffer inputs into internal register to store for future cycles
always_ff @(posedge clk or negedge reset_n) begin
  if(!reset_n) begin
    reset();
  end
  else begin
    for (i = 0; i<16; i++) begin
      internal_products[i] <= products[i];
    end
    for (i = 0; i< TILE_SIZE; i++) begin
      internal_row_coordinate[i] <= row_coordinate[i];
      internal_column_coordinate[i] <= column_coordinate[TILE_SIZE];
    end
  end
end
*/

task reset();
  crossbar_stall <= 0;
  inputs_sent <= 0;
  for(i = 0; i<BANK_COUNT; i++) begin
    buffer_write_enable[i] <= 0;
    buffer_data_write[i] <= 0;
    buffer_column_write[i] <= 0;
    buffer_row_write[i] <= 0;
  end
endtask

task route();
  for(i = 0; i<BANK_COUNT; i++) begin
    buffer_write_enable[i] <= next_buffer_write_enable[i];
    buffer_data_write[i] <= next_buffer_data_write[i];
    buffer_column_write[i] <= next_buffer_column_write[i];
    buffer_row_write[i] <= next_buffer_row_write[i];
    inputs_sent <= inputs_sent | next_inputs_sent;
    //Handle stall signal and reset the inputs_sent 
    case(bitwidth)
      2'b10:
        begin
          if (inputs_sent == 0) begin
            crossbar_stall <= 0;
          end
          else begin
            if (inputs_sent ^ 65535 > 0) begin
              crossbar_stall <= 1;
            end
            else begin
              reset();
            end
          end
        end
      default: crossbar_stall <= 0;
    endcase 
  end
endtask

always @(posedge clk or negedge reset_n) begin
  if(!reset_n) begin
    reset();
  end
  else begin
    route();
  end
end

endmodule

