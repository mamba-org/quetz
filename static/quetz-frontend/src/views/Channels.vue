<template>
<div class="bx--grid">
  <div class="bx--row">
    <div class="bx--col-lg-13 bx--offset-lg-3">
        <h1 v-on:click="onRowClicked">Channels</h1>
        <cv-data-table :columns="columns" :data="data" ref="table">
          <template slot="data">
            <cv-data-table-row v-for="(row, rowIndex) in data" :key="`${rowIndex}`" :value="`${rowIndex}`">
               <cv-data-table-cell>{{ row[0] }}</cv-data-table-cell>
               <cv-data-table-cell>{{ row[1] }}</cv-data-table-cell>
               <cv-data-table-cell><Password16 v-if="row[2]" class="white-svg"/></cv-data-table-cell>
            </cv-data-table-row>
          </template>
        </cv-data-table>
    </div>
  </div>
</div>
</template>

<script>
  import Password16 from '@carbon/icons-vue/es/password/16';

  export default {
    components: {
      Password16
    },
    data: function () {
      return {
        columns: [],
        data: [],
        loading: true,
        rowSelects: []
      }
    },
    methods: {
      fetchData: function() {
        return fetch("/api/channels").then((msg) => {
          console.log(msg);
          return msg.json().then((decoded) => {
              this.columns = ["Name", "Description", "Private"];
              this.data = decoded.map((el) => [el.name, el.description, el.private]);
          });
        });
      },
      attachEvents: function() {
        let router = this.$router;
        this.$el.querySelectorAll('tr').forEach((el) => {
          el.addEventListener('click', () => {
            router.push({ path: "/channel/" + this.data[el.getAttribute('value')][0] + "/packages"});
          });
        });
      },
      actionRowSelectChange: function() {
        console.log(arguments);
      },
      onRowClicked: function() {
        console.log("Row clickedididi");
      }
    },
    created: function() {
      this.fetchData();
    },
    mounted() {
    },
    updated() {
      this.attachEvents();
    }
}
</script>

<style>
html {
   height: 100%;
}

body, #app {
   min-height: 100%;
}

.white-svg {
  fill: white;
}

</style>

<style scoped>
tbody tr {
  cursor: pointer;
}
</style>